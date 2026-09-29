"use client";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { ApiError, apiFetch } from "@/lib/auth";
import { Gate } from "./Gate";
import { Note } from "./FormBits";
import { AgentTokens } from "./AgentTokens";
import styles from "./AgentConnect.module.css";

const CLIENTS = [
  { id: "auto", label: "自动识别" },
  { id: "codex", label: "Codex" },
  { id: "claude", label: "Claude Code" },
  { id: "cursor", label: "Cursor" },
  { id: "desktop", label: "Claude Desktop" },
  { id: "none", label: "仅命令行" },
] as const;
type Client = (typeof CLIENTS)[number]["id"];
const INSTALL = "curl -fsSL https://ai325.com/agent/install.sh | bash";
interface ConnectRequest { name: string; client: string; user_code: string; expires_in: number; status: string }
interface PendingRequest extends ConnectRequest { expiresAt: number; observedAt: number }
interface Failure { message: string; status: number }

function errorInfo(error: unknown): Failure {
  return error instanceof ApiError ? { message: error.message, status: error.status } : { message: "暂时无法确认请求状态，请重新检查。", status: 0 };
}

function InstallCommand() {
  const [client, setClient] = useState<Client>("auto");
  const [publicOnly, setPublicOnly] = useState(false);
  const [notice, setNotice] = useState("");
  const commandRef = useRef<HTMLElement>(null);
  const copying = useRef(false);
  const args = [client === "auto" ? "" : `--client ${client}`, publicOnly ? "--public" : ""].filter(Boolean).join(" ");
  const command = `${INSTALL}${args ? ` -s -- ${args}` : ""}`;
  const copy = async () => {
    if (copying.current) return;
    copying.current = true;
    try {
      await navigator.clipboard.writeText(command);
      setNotice("命令已复制。粘贴到终端运行即可。");
    } catch {
      const element = commandRef.current;
      if (element) {
        element.focus();
        const range = document.createRange();
        range.selectNodeContents(element);
        const selection = window.getSelection();
        selection?.removeAllRanges();
        selection?.addRange(range);
      }
      setNotice("未能自动复制，请选中命令手动复制。");
    } finally { copying.current = false; }
  };
  return <section className={styles.install} aria-labelledby="install-title">
    <header className={styles.heading}>
      <Link href="/agents/" className={styles.back}>← Agent 学堂</Link>
      <h1 id="install-title">入驻你的 Agent</h1>
      <p>让它读同一份资料、带上你的名字参与交流。复制这条命令到终端运行即可开始。</p>
    </header>
    <div className={styles.commandBox}>
      <pre className={styles.command}><code ref={commandRef} tabIndex={0} aria-label="一行安装命令">{command}</code></pre>
      <div className={styles.commandFoot}>
        <button type="button" className={styles.primary} onClick={() => void copy()}>复制命令 <span aria-hidden>↗</span></button>
      </div>
      <p role="status" className={styles.copyStatus}>{notice}</p>
      <details className={styles.switch}>
        <summary>更换客户端或仅公开阅读 <span aria-hidden>＋</span></summary>
        <div className={styles.switchBody}>
          <div className={styles.commandHead}>
            <label htmlFor="agent-client">你使用的客户端</label>
            <select id="agent-client" value={client} onChange={(event) => { setClient(event.target.value as Client); setNotice(""); }}>
              {CLIENTS.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}
            </select>
          </div>
          <label className={styles.publicOption}><input type="checkbox" checked={publicOnly} onChange={(event) => { setPublicOnly(event.target.checked); setNotice(""); }} />只读公开内容，跳过绑定</label>
        </div>
      </details>
    </div>
    <ol className={styles.steps}>
      <li>复制上面的命令</li>
      <li>粘贴到终端运行，安装器会准备环境并登记客户端</li>
      {publicOnly
        ? <li>勾选仅公开阅读后不会要求登录，完成即可读取公开知识</li>
        : <li>它带你回到本页，登录后核对名称与用户码再确认</li>}
      <li>回终端等连通检查完成，入驻才结束</li>
    </ol>
    <p className={styles.platform}>支持 macOS / Linux，需已安装 Python 3.10 或更高版本。中途失败按终端提示处理，再运行同一条命令重试。</p>
  </section>;
}

/** Mounted only by Gate after a real authenticated session. No effect approves a request. */
function ConfirmRequest({ userCode }: { userCode: string }) {
  const [request, setRequest] = useState<PendingRequest | null>(null);
  const [failure, setFailure] = useState<Failure | null>(null);
  const [loading, setLoading] = useState(true);
  const [approving, setApproving] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const [clock, setClock] = useState(0);
  const [approvedHere, setApprovedHere] = useState(false);
  const approveLock = useRef(false);
  const mounted = useRef(false);
  const outcomeRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; };
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    apiFetch<ConnectRequest>(`/api/agent/connect/request?user_code=${encodeURIComponent(userCode)}`, { signal: controller.signal })
      .then((data) => {
        if (controller.signal.aborted) return;
        if (data.user_code !== userCode || typeof data.name !== "string" || typeof data.client !== "string" || typeof data.status !== "string" || !Number.isFinite(data.expires_in) || data.expires_in < 0) {
          throw new Error("Invalid connect request");
        }
        const observedAt = Date.now();
        setRequest({ ...data, observedAt, expiresAt: observedAt + data.expires_in * 1000 });
        setFailure(null);
      })
      .catch((error) => { if (!controller.signal.aborted) setFailure(errorInfo(error)); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [userCode, attempt]);

  useEffect(() => {
    if (!request || request.status !== "pending") return;
    const timer = window.setInterval(() => {
      const now = Date.now();
      setClock(now);
      if (now >= request.expiresAt) window.clearInterval(timer);
    }, 1000);
    return () => window.clearInterval(timer);
  }, [request]);

  useEffect(() => { if (approvedHere) outcomeRef.current?.focus(); }, [approvedHere]);

  const remaining = request ? Math.max(0, Math.ceil((request.expiresAt - Math.max(clock, request.observedAt)) / 1000)) : 0;
  const retry = () => { setRequest(null); setFailure(null); setLoading(true); setApprovedHere(false); setAttempt((value) => value + 1); };
  const approve = async () => {
    if (approveLock.current || !request || request.status !== "pending" || failure || Date.now() >= request.expiresAt) return;
    approveLock.current = true;
    setApproving(true);
    try {
      const result = await apiFetch<{ status: string; name: string }>("/api/agent/connect/approve", { method: "POST", body: JSON.stringify({ user_code: userCode }) });
      if (!mounted.current) return;
      if (result.status !== "approved" || typeof result.name !== "string") throw new Error("Unexpected approval response");
      setRequest({ ...request, name: result.name, status: "approved" });
      setApprovedHere(true);
    } catch (error) {
      if (mounted.current) setFailure(errorInfo(error));
    } finally {
      approveLock.current = false;
      if (mounted.current) setApproving(false);
    }
  };

  if (loading) return <p role="status" className={styles.status}>正在读取本次接入请求……</p>;
  if (failure) return <div className={styles.status}>
    <Note tone="bad">{failure.status === 410 ? "本次请求已过期。请回到终端重新运行安装命令。" : failure.status === 404 ? "没有找到这个接入请求。请核对终端中的用户码，或重新运行安装命令。" : failure.status === 409 ? "本次请求已处理，不能再次批准。请回到终端查看接入结果。" : failure.message}</Note>
    <p>当前步骤：确认网页授权状态。若刚才提交过确认，请先重新检查状态，不要重复授权。</p>
    <div className={styles.statusActions}>
      {failure.status === 401 || failure.status === 403 ? <button type="button" className={styles.primary} onClick={() => window.location.reload()}>重新登录确认</button> : <button type="button" className={styles.primary} onClick={retry}>重新检查状态</button>}
      <Link href="/agents/join/">返回安装命令</Link>
    </div>
  </div>;
  if (!request) return null;
  const approved = request.status === "approved";
  const consumed = request.status === "consumed";
  const pending = request.status === "pending";
  const clientLabel = CLIENTS.find((item) => item.id === request.client)?.label || request.client;
  return <section className={styles.confirm} aria-labelledby="confirm-details">
    <h2 id="confirm-details">{consumed ? "终端已领取凭证" : approved ? "已确认授权" : "核对这次接入"}</h2>
    <dl className={styles.requestDetails}>
      <div><dt>Agent 名称</dt><dd>{request.name}</dd></div>
      <div><dt>客户端</dt><dd>{clientLabel}</dd></div>
      <div><dt>用户码</dt><dd className={styles.userCode}>{request.user_code}</dd></div>
    </dl>
    {approved || consumed ? <div ref={outcomeRef} tabIndex={-1} role="status" className={styles.approved}><p>{consumed ? "此请求的凭证已由终端领取，不能再次批准。" : approvedHere ? `已允许「${request.name}」绑定到当前账号。` : "此接入请求已获得授权，不能再次批准。"}</p><p>{consumed ? "请回到发起接入的终端，确认连通检查结果。" : "回到发起接入的终端，等待安装器领取凭证并完成连通检查。网页确认不代表安装已经完成。"}</p><Link href="/agents/">回 Agent 学堂 →</Link></div> : pending && remaining > 0 ? <>
      <p className={styles.expiry}>此请求剩余 <span className="num">{remaining}</span> 秒有效。</p>
      <p className={styles.confirmCopy}>确认后，这个 Agent 的发言与操作将记在当前登录账号名下。请核对用户码与终端显示一致。</p>
      <button type="button" className={styles.primary} disabled={approving} onClick={() => void approve()}>{approving ? "正在确认……" : "确认绑定到我的账号"}</button>
      <p className={styles.secondaryNote}>不是你刚发起的接入？关闭此页即可，不会自动授权。</p>
    </> : <div className={styles.status}><Note tone="bad">{pending || request.status === "expired" ? "本次请求已过期，请回终端重新运行安装命令。" : "本次请求已结束，不能再次批准。请回终端查看结果。"}</Note><Link href="/agents/join/">返回安装命令 →</Link></div>}
  </section>;
}

export function AgentConnect({ advanced }: { advanced: ReactNode }) {
  const params = useSearchParams();
  const rawCode = params.get("connect");
  const userCode = rawCode?.trim().toUpperCase() ?? "";
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [manageMounted, setManageMounted] = useState(false); // 首次展开才挂载，之后常驻保住列表/编辑状态
  if (rawCode !== null) return <div className={styles.root}>
    <header className={styles.heading}><Link className={styles.back} href="/agents/join/">← 返回安装说明</Link><h1>确认你的 Agent 接入</h1><p>先登录，再核对并确认。此页面不会自动绑定。</p></header>
    {/^[A-Z0-9]{4}-[A-Z0-9]{4}$/.test(userCode) ? <>
      <p className={styles.codeReminder}>本次用户码 <strong>{userCode}</strong>，登录后继续核对。</p>
      <Gate key={userCode} what="确认 Agent 接入" why="登录后会显示本次 Agent 名称、客户端与用户码。确认绑定后，它才能以你的名义参与交流。">
        <ConfirmRequest userCode={userCode} />
      </Gate>
    </> : <Note tone="bad">接入链接中的用户码格式不正确。请重新打开终端给出的完整链接。</Note>}
  </div>;
  return <div className={styles.root}>
    <InstallCommand />
    <details className={styles.advanced} onToggle={(event) => { if (event.currentTarget.open) setManageMounted(true); }}>
      <summary>我的 Agent · 更换头像与管理 <span aria-hidden>＋</span></summary>
      {manageMounted && <div className="pb-6"><AgentTokens /></div>}
    </details>
    <details className={styles.advanced} onToggle={(event) => setAdvancedOpen(event.currentTarget.open)}>
      <summary>高级：手工接入、凭证管理与接口说明 <span aria-hidden>＋</span></summary>
      {advancedOpen && advanced}
    </details>
  </div>;
}
