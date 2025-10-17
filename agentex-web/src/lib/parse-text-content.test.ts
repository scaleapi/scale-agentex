import {expect} from 'chai';
import {parseTextContent} from './parse-text-content';

describe('parseTextContent', () => {
  describe('basic functionality', () => {
    it('should handle primitive values', async () => {
      expect(await parseTextContent('hello')).to.equal('hello');
      expect(await parseTextContent(42)).to.equal(42);
      expect(await parseTextContent(true)).to.equal(true);
      expect(await parseTextContent(false)).to.equal(false);
      expect(await parseTextContent(null)).to.equal(null);
    });

    it('should handle undefined values', async () => {
      expect(await parseTextContent(undefined)).to.be.undefined;
    });

    it('should handle arrays', async () => {
      const result = await parseTextContent([1, 'hello', true, null]);
      expect(result).to.deep.equal([1, 'hello', true, null]);
    });

    it('should handle objects', async () => {
      const obj = {name: 'test', value: 42, active: true};
      const result = await parseTextContent(obj);
      expect(result).to.deep.equal(obj);
    });

    it('should handle nested structures', async () => {
      const nested = {
        user: {
          name: 'John',
          preferences: ['dark', 'compact'],
          settings: {theme: 'dark', lang: 'en'},
        },
      };
      const result = await parseTextContent(nested);
      expect(result).to.deep.equal(nested);
    });
  });

  describe('JSON string parsing', () => {
    it('should parse valid JSON strings', async () => {
      const jsonString = '{"name": "test", "value": 42}';
      const result = await parseTextContent(jsonString);
      expect(result).to.deep.equal({name: 'test', value: 42});
    });

    it('should handle nested JSON strings', async () => {
      const nestedJson = '{"data": {"items": [1, 2, 3]}}';
      const result = await parseTextContent(nestedJson);
      expect(result).to.deep.equal({data: {items: [1, 2, 3]}});
    });

    it('should treat invalid JSON as regular strings', async () => {
      const invalidJson = '{"invalid": json}';
      const result = await parseTextContent(invalidJson);
      expect(result).to.equal(invalidJson);
    });

    it('should not parse JSON primitive strings', async () => {
      expect(await parseTextContent('"hello"')).to.equal('"hello"');
      expect(await parseTextContent('42')).to.equal('42');
      expect(await parseTextContent('true')).to.equal('true');
    });
  });

  describe('depth limit handling', () => {
    it('should respect depth limit for objects', async () => {
      const deepObject = {level1: {level2: {level3: 'deep'}}};
      const result = await parseTextContent(deepObject, {
        depthLimit: 0,
        sizeLimit: 1024 * 1024,
        yieldControlEvery: 10,
      });

      expect(result).to.be.an('object').and.not.be.null;
      expect(result).to.have.property('level1');
      expect((result as {level1: unknown}).level1).to.be.a('string');
    });

    it('should respect depth limit for arrays', async () => {
      const deepArray = [[[['deep']]]];
      const result = await parseTextContent(deepArray, {
        depthLimit: 0,
        sizeLimit: 1024 * 1024,
        yieldControlEvery: 10,
      });

      expect(Array.isArray(result)).to.be.true;
      expect((result as unknown[])[0]).to.be.a('string');
    });
  });

  describe('size limit handling', () => {
    it('should truncate long strings', async () => {
      const longString = 'a'.repeat(1000);
      const result = await parseTextContent(longString, {
        depthLimit: 256,
        sizeLimit: 100,
        yieldControlEvery: 10,
      });
      expect(typeof result).to.equal('string');
      expect(result).to.include('truncated');
    });

    it('should truncate arrays when size limit exceeded', async () => {
      const largeArray = Array(1000).fill('test');
      const result = await parseTextContent(largeArray, {
        depthLimit: 256,
        sizeLimit: 100,
        yieldControlEvery: 10,
      });
      expect(Array.isArray(result)).to.be.true;
      const castedResult = result as unknown[];
      expect(castedResult[castedResult.length - 1])
        .to.be.a('string')
        .and.to.include('truncated');
    });

    it('should truncate objects when size limit exceeded', async () => {
      const largeObject: Record<string, string> = {};
      for (let i = 0; i < 1000; i++) {
        largeObject[`key${i}`] = `value${i}`;
      }
      const result = await parseTextContent(largeObject, {
        depthLimit: 256,
        sizeLimit: 100,
        yieldControlEvery: 10,
      });
      expect(result).to.have.property('TRUNCATED');
    });
  });

  describe('circular reference detection', () => {
    it('should detect circular references in objects', async () => {
      const circularObj: Record<string, unknown> = {name: 'test'};
      circularObj.self = circularObj;

      const result = await parseTextContent(circularObj);
      expect(result).to.deep.be.an('object').and.not.be.null;
    });

    it('should detect circular references in arrays', async () => {
      const circularArray: unknown[] = [1, 2];
      circularArray.push(circularArray);

      const result = await parseTextContent(circularArray);
      expect(Array.isArray(result)).to.be.true;
      expect((result as unknown[]).slice(0, 2)).to.deep.equal([1, 2]);
    });

    it('should handle complex circular structures', async () => {
      const obj1: Record<string, unknown> = {name: 'obj1'};
      const obj2: Record<string, unknown> = {name: 'obj2', ref: obj1};
      obj1.ref = obj2;

      const result = await parseTextContent(obj1);
      expect(result).to.be.an('object').and.to.not.be.null;
      const castedResult = result as Record<string, unknown>;
      expect(castedResult.name).to.equal(obj1.name);
      expect(castedResult.ref).to.be.an('object').and.to.not.be.null;
      const castedNestedRef = castedResult.ref as Record<string, unknown>;
      expect(castedNestedRef.name).to.equal(obj2.name);
      expect(castedNestedRef.ref).to.be.a('string');
    });
  });

  describe('edge cases', () => {
    it('should handle empty arrays', async () => {
      const result = await parseTextContent([]);
      expect(result).to.deep.equal([]);
    });

    it('should handle empty objects', async () => {
      const result = await parseTextContent({});
      expect(result).to.deep.equal({});
    });

    it('should handle arrays with undefined values', async () => {
      const arr = [1, undefined, 3];
      const result = await parseTextContent(arr);
      expect(result).to.deep.equal([1, 3]);
    });

    it('should handle objects with undefined values', async () => {
      const obj = {a: 1, b: undefined, c: 3};
      const result = await parseTextContent(obj);
      expect(result).to.deep.equal({a: 1, c: 3});
    });

    it('should handle functions', async () => {
      const fn = () => 'test';
      const result = await parseTextContent(fn);
      expect(result).to.be.undefined;
    });

    it('should handle symbols', async () => {
      const sym = Symbol('test');
      const result = await parseTextContent(sym);
      expect(result).to.be.undefined;
    });
  });

  describe('yield control', () => {
    it('should yield control at specified intervals', async () => {
      const largeArray = Array(16)
        .fill(0)
        .map((_, i) => ({index: i}));

      const baseConfigs = {
        depthLimit: 256,
        sizeLimit: 1024 * 1024,
      };

      const frequentYieldStartTime = Date.now();
      await parseTextContent(largeArray, {
        ...baseConfigs,
        yieldControlEvery: 1,
      });
      const frequentYieldRuntime = Date.now() - frequentYieldStartTime;

      const noYieldStartTime = Date.now();
      await parseTextContent(largeArray, {
        ...baseConfigs,
        yieldControlEvery: largeArray.length * 2,
      });
      const noYieldRuntime = Date.now() - noYieldStartTime;

      // heuristic: difference in execution time should be at least about 1 ms per yield
      // on my machine it's about 2 ms per yield
      expect(frequentYieldRuntime - noYieldRuntime).to.be.greaterThan(largeArray.length);
    });
  });
});
