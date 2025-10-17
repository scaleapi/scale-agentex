type JsonCompatiblePrimitive = string | number | boolean | null;
type JsonCompatibleValue =
  | JsonCompatiblePrimitive
  | JsonCompatibleValue[]
  | {[key: string]: JsonCompatibleValue};

type ParseTextContentConfigs = {
  depthLimit: number;
  sizeLimit: number;
  yieldControlEvery: number;
};

class RecursiveParser {
  private parentObjects: WeakSet<object>;
  private totalSize: number;

  constructor(private configs: ParseTextContentConfigs) {
    this.parentObjects = new WeakSet();
    this.totalSize = 0;
  }

  async recurse(value: unknown, depth: number): Promise<JsonCompatibleValue | undefined> {
    // note that this function increases total size whenever it returns a primitive
    if (typeof value === 'string') {
      if (this.totalSize + value.length > this.configs.sizeLimit) {
        const truncatedValue =
          value.substring(0, this.totalSize - value.length) + ' (truncated)';

        this.totalSize += truncatedValue.length;
        return truncatedValue;
      }

      try {
        const parsed = JSON.parse(value);
        if (typeof parsed === 'object' && parsed !== null) {
          return await this.recurse(parsed, depth + 1);
        }
      } catch {}

      this.totalSize += value.length;
      return value;
    }

    // special cases for objects
    if (typeof value === 'object' && value !== null) {
      if (this.parentObjects.has(value)) {
        return 'Circular reference';
      }
      if (depth > this.configs.depthLimit) {
        return 'Maximum object depth reached';
      }

      // Yield control periodically
      if (depth % this.configs.yieldControlEvery === 0) {
        await new Promise(resolve => setTimeout(resolve, 0));
      }
    }

    if (Array.isArray(value)) {
      // prevent circular references
      this.parentObjects.add(value);

      const results: JsonCompatibleValue[] = [];

      for (let i = 0; i < value.length; i++) {
        // truncate when exceeding size limit
        if (this.totalSize > this.configs.sizeLimit) {
          const truncationMessage = `${value.length - i} items were truncated due to size`;
          this.totalSize += truncationMessage.length;
          results.push(truncationMessage);
          break;
        }
        const parsedItem = await this.recurse(value[i], depth + 1);

        // omit undefined
        if (parsedItem !== undefined) {
          results.push(parsedItem);
        }

        // Yield control periodically
        if (i % this.configs.yieldControlEvery === 0) {
          await new Promise(resolve => setTimeout(resolve, 0));
        }
      }

      this.parentObjects.delete(value);
      return results;
    }

    if (typeof value === 'object' && value !== null) {
      // prevent circular references
      this.parentObjects.add(value);

      const result: Record<string, JsonCompatibleValue> = {};

      const entries = Object.entries(value);

      for (let i = 0; i < entries.length; i++) {
        const [key, subValue] = entries[i];

        // truncate when exceeding size limit
        if (this.totalSize > this.configs.sizeLimit) {
          const truncationKey = 'TRUNCATED';
          const truncationValue = `${entries.length - i} fields were truncated due to size`;
          this.totalSize += truncationKey.length + truncationValue.length;
          result[truncationKey] = truncationValue;
          break;
        }

        const parsedValue = await this.recurse(subValue, depth + 1);

        // omit undefined
        if (parsedValue !== undefined) {
          result[key] = parsedValue;
        }

        // Yield control periodically
        if (i % this.configs.yieldControlEvery === 0) {
          await new Promise(resolve => setTimeout(resolve, 0));
        }
      }

      this.parentObjects.delete(value);

      return result;
    }

    if (typeof value === 'number' || typeof value === 'boolean' || value === null) {
      this.totalSize += 8;
      return value;
    }

    return undefined;
  }
}

/** used to parse some large and unknown value into JSON if possible */
export function parseTextContent(
  value: unknown,
  configs: ParseTextContentConfigs = {
    depthLimit: 256,
    // 1 MB
    sizeLimit: 1025 * 1024,
    yieldControlEvery: 10,
  }
): Promise<JsonCompatibleValue | undefined> {
  const parser = new RecursiveParser(configs);
  return parser.recurse(value, 0);
}
