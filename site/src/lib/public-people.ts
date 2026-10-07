import type { Tone } from "./shared";

export interface Person {
  name: string; slug: string; aliases: string[]; role: string; msgs: number;
  tone: Tone; quote: string; tags: string[]; avatar: string | null; wxid?: string;
}

export function resolvePerson(people: Person[], query: string): Person | undefined {
  const key = query.trim();
  if (!key) return;
  const ids = people.filter((person) => person.wxid === key);
  if (ids.length) return ids.length === 1 ? ids[0] : undefined;
  const exact = people.filter((person) => person.name === key);
  const matches = exact.length ? exact : people.filter((person) => person.aliases.includes(key));
  return matches.length === 1 ? matches[0] : undefined;
}

export function createPeopleLoader(fetcher: typeof fetch) {
  let cache: Person[] | null = null;
  let inflight: Promise<Person[]> | null = null;
  return function loadPeople(): Promise<Person[]> {
    if (cache) return Promise.resolve(cache);
    if (!inflight) inflight = fetcher("/people.json", { cache: "no-cache" })
      .then(async (response) => {
        if (!response.ok) throw new Error("Member directory unavailable");
        const data: unknown = await response.json();
        if (!Array.isArray(data) || data.some((p) => !p || typeof p.name !== "string" || typeof p.slug !== "string" || !Array.isArray(p.aliases))) {
          throw new Error("Invalid member directory");
        }
        return (cache = data as Person[]);
      })
      .catch(() => []) // A failed request must not poison subsequent navigations.
      .finally(() => { inflight = null; });
    return inflight;
  };
}

export const loadPeople = createPeopleLoader((...args) => fetch(...args));
