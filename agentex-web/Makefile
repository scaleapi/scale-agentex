.PHONY: install

install:
	npm install

dev: install
	npm run dev

build:
	NEXT_IGNORE_ESLINT_ERRORS=true npx next build --no-lint

storybook: install
	npm run storybook
