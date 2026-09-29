export interface LibrarySkill {
  id: string;
  name: string;
  description: string;
  category: string;
  tags: string[];
  author: string;
  license: string;
  sourceUrl: string | null;
  downloadUrl: string | null;
  packageBytes: number | null;
  sha256: string | null;
  status: string;
  detailUrl?: string;
  hasEditorial?: boolean;
  repositoryUrl?: string | null;
  repositoryStars?: number | null;
  starsCheckedAt?: string | null;
}
export interface SkillLibraryData {
  schemaVersion: 1;
  generatedAt: string;
  items: LibrarySkill[];
}

export interface SkillEditorial {
  overview: string;
  useCases: string[];
  inputs: string[];
  outputs: string[];
  steps: string[];
  limitations: string[];
  reviewedAt: string;
  sourceUrl?: string;
}
export interface SkillDetail {
  skillMarkdown: string | null;
  sourceUrl: string | null;
  repositoryUrl: string | null;
  editorial?: SkillEditorial;
}
