export { add } from "./math";

export function formatName(name: string): string {
  return name.trim().toUpperCase();
}

export class Cache<T> {
  private items = new Map<string, T>();

  get(key: string): T | undefined {
    return this.items.get(key);
  }

  getOr(key: string, fallback: T): T {
    return this.get(key) ?? fallback;
  }
}
