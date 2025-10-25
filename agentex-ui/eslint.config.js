const { FlatCompat } = require('@eslint/eslintrc');
const reactHooks = require('eslint-plugin-react-hooks');
const prettierPlugin = require('eslint-plugin-prettier');

const compat = new FlatCompat({
  baseDirectory: __dirname,
});

module.exports = [
  {
    ignores: [
      '.next/**',
      'node_modules/**',
      'eslint.config.js',
      'postcss.config.mjs',
      'next.config.ts',
      'next-env.d.ts',
    ],
  },
  ...compat.extends('next/core-web-vitals', 'next/typescript', 'prettier'),
  {
    plugins: {
      'react-hooks': reactHooks,
      prettier: prettierPlugin,
    },
    languageOptions: {
      parserOptions: {
        tsconfigRootDir: __dirname,
        project: './tsconfig.json',
        sourceType: 'module',
      },
    },
    settings: {
      'import/resolver': {
        typescript: {
          project: './tsconfig.json',
        },
        node: {
          extensions: ['.js', '.jsx', '.ts', '.tsx'],
        },
      },
    },
    rules: {
      eqeqeq: ['error', 'smart'],
      '@typescript-eslint/no-misused-promises': [
        'error',
        { checksVoidReturn: false },
      ],
      '@typescript-eslint/no-unsafe-return': 'off',
      '@typescript-eslint/require-await': 'off',
      '@typescript-eslint/no-explicit-any': 'error',
      '@typescript-eslint/no-unsafe-assignment': 'off',
      '@typescript-eslint/no-unsafe-call': 'off',
      '@typescript-eslint/no-unused-vars': [
        'error',
        {
          argsIgnorePattern: '_',
          varsIgnorePattern: '_',
          args: 'all',
        },
      ],
      'filenames/match-regex': 'off',
      'filenames/match-exported': 'off',
      'prettier/prettier': 'error',
      'import/no-anonymous-default-export': 'off',
      'react-hooks/rules-of-hooks': 'error',
      'react-hooks/exhaustive-deps': 'warn',
      'import/no-extraneous-dependencies': [
        'error',
        {
          devDependencies: ['**/*.test.ts'],
        },
      ],
      'no-console': ['error', { allow: ['warn', 'error'] }],
      'no-else-return': 'error',
      'prefer-const': 'error',
      'no-var': 'error',
      
      // Import sorting and organization
      'import/order': [
        'warn',
        {
          groups: [
            'builtin',        // Node.js built-in modules (fs, path, etc.)
            'external',       // npm packages (react, next, etc.)
            'internal',       // Aliased imports (@/...)
            ['parent', 'sibling'], // Relative imports (../, ./)
            'index',          // Index imports (./)
            'type',           // TypeScript type imports
          ],
          pathGroups: [
            {
              pattern: 'react',
              group: 'external',
              position: 'before',
            },
            {
              pattern: 'next/**',
              group: 'external',
              position: 'before',
            },
            {
              pattern: '@/**',
              group: 'internal',
              position: 'before',
            },
          ],
          pathGroupsExcludedImportTypes: ['builtin'],
          'newlines-between': 'always',
          alphabetize: {
            order: 'asc',
            caseInsensitive: true,
          },
          warnOnUnassignedImports: false,
        },
      ],
      'import/no-duplicates': 'error',
      'import/newline-after-import': 'warn',
      'import/first': 'error',
    },
  },
];
