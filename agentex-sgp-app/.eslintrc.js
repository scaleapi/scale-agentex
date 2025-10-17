const level = {
  DISABLE: 0,
  WARN: 1,
  ERROR: 2,
};

module.exports = {
  extends: ['next/core-web-vitals', 'next/typescript', 'prettier'],
  parserOptions: {
    tsconfigRootDir: __dirname,
    project: ['./tsconfig.json', './cypress/tsconfig.json'],
    sourceType: 'module',
  },
  plugins: ['react-hooks', 'prettier'],
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
      level.ERROR,
      { checksVoidReturn: false },
    ],
    '@typescript-eslint/no-unsafe-return': [level.DISABLE],
    '@typescript-eslint/require-await': [level.DISABLE],
    'filenames/match-regex': [level.DISABLE],
    'filenames/match-exported': [level.DISABLE],
    'prettier/prettier': [level.ERROR],
    '@typescript-eslint/no-unused-vars': [
      level.ERROR,
      {
        argsIgnorePattern: '_',
        varsIgnorePattern: '_',
        args: 'all',
      },
    ],
    '@typescript-eslint/no-explicit-any': [level.ERROR],
    'import/no-anonymous-default-export': [level.DISABLE],
    'react-hooks/rules-of-hooks': [level.ERROR],
    'react-hooks/exhaustive-deps': [level.WARN],
    '@typescript-eslint/no-unsafe-assignment': [level.DISABLE],
    '@typescript-eslint/no-unsafe-call': [level.DISABLE],
    'import/no-extraneous-dependencies': [
      level.ERROR,
      {
        devDependencies: ['**/*.test.ts'],
      },
    ],
  },
};
