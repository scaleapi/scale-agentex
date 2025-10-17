import type {Meta, StoryObj} from '@storybook/nextjs';

import {AttachmentChip} from './attachment-chip';

import '@/app/globals.css';

const meta = {
  title: 'kit/AttachmentChip',
  component: AttachmentChip,
  parameters: {
    layout: 'centered',
  },
  tags: ['autodocs'],
  argTypes: {
    name: {control: 'text'},
    contentType: {control: 'text'},
    size: {
      control: {
        type: 'select',
        options: ['xs', 'sm', 'md', 'lg'],
      },
    },
    className: {control: 'text'},
  },
} satisfies Meta<typeof AttachmentChip>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Text: Story = {
  args: {
    name: 'example.txt',
    contentType: 'text/plain',
  },
};

export const Image: Story = {
  args: {
    name: 'image.png',
    contentType: 'image/png',
  },
};

export const Audio: Story = {
  args: {
    name: 'audio.mp3',
    contentType: 'audio/mpeg',
  },
};

export const Video: Story = {
  args: {
    name: 'video.mp4',
    contentType: 'video/mp4',
  },
};

export const Unknown: Story = {
  args: {
    name: 'blob.bin',
    contentType: 'application/octet-stream',
  },
};
