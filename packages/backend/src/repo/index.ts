import { config } from '../lib/config';
import { MemoryRepo } from './memory';
import { DynamoRepo } from './dynamo';
import type { Repo } from './types';

let cached: Repo | undefined;

/** 依 REPO_DRIVER 決定實作，Lambda 冷啟後重複使用 */
export function getRepo(): Repo {
  if (!cached) {
    cached = config.repoDriver === 'dynamodb' ? new DynamoRepo() : new MemoryRepo();
  }
  return cached;
}

export type { Repo };
