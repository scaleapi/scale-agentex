# Agentex UI Kit

This directory contains the source code for all Agentex UI Kit components. These components are inspired by [shadcn/ui](https://ui.shadcn.com) and are designed to be plugged into other React apps.

## Guidelines

1. Follow [shadcn/ui](https://ui.shadcn.com) practices
   1. [Tailwind CSS](https://tailwindcss.com)
   2. `import { cn } from "@/lib/utils"` for managing Tailwind classes
   3. `dark:...` for dark-theme CSS
2. Components should be defined a single file
3. Prefer using other Agentex UI Kit and shadcn/ui components as dependencies
   1. Other npm dependencies are fine too
4. Avoid outside context
   1. Avoid using outer React context unless your component creates its own context
   2. Avoid making API calls
5. Outside context should come from props
   1. For example, `fileDownloadAction` or `onDownloadFile`
6. Minimize state
7. No global variables
8. Avoid forwarding / consuming refs
9. Do not use a default export

## Development

agentex-web can use these components directly since they exist in the same monolith.

TODO: we would like to publish a `shadcn/ui` registry so that developers can use the `shadcn` CLI tool to add these components into other projects.

Create [Storybook](https://storybook.js.org) stories next to your components.

TODO: publish Storybook
