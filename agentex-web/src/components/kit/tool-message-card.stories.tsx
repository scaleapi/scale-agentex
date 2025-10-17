import type {Meta, StoryObj} from '@storybook/nextjs';

import {ToolMessageCard} from './tool-message-card';

import '@/app/globals.css';

const meta = {
  title: 'kit/ToolMessageCard',
  component: ToolMessageCard,
  parameters: {
    layout: 'centered',
  },
  tags: ['autodocs'],
  argTypes: {
    name: {control: 'text'},
    content: {control: 'object'},
    variant: {
      control: 'select',
      options: ['request', 'response'],
    },
    activityStatus: {control: 'select', options: ['static', 'active']},
    className: {control: 'text'},
  },
} satisfies Meta<typeof ToolMessageCard>;

export default meta;
type Story = StoryObj<typeof meta>;

export const CompleteRequest: Story = {
  args: {
    name: 'search',
    content: `{"query": "What is agentex?"}`,
    variant: 'request',
    activityStatus: 'static',
  },
};

export const PendingRequest: Story = {
  args: {
    name: 'search',
    content: `{"query": "What is agentex?"}`,
    variant: 'request',
    activityStatus: 'active',
  },
};

export const CompleteResponse: Story = {
  args: {
    name: 'search',
    content: `Agentex is a platform for building AI agents.`,
    variant: 'response',
    activityStatus: 'static',
  },
};

export const PendingResponse: Story = {
  args: {
    name: 'search',
    content: undefined,
    variant: 'response',
    activityStatus: 'active',
  },
};

export const NullResponse: Story = {
  args: {
    name: 'search',
    content: null,
    variant: 'response',
    activityStatus: 'static',
  },
};
