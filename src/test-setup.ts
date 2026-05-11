import '@testing-library/jest-dom';
import { vi } from 'vitest';

// next/navigation hooks need a router context that vitest can't provide; mock
// them globally so client components using useRouter / usePathname render.
vi.mock('next/navigation', () => ({
  useRouter: () => ({
    refresh: vi.fn(),
    push: vi.fn(),
    replace: vi.fn(),
    back: vi.fn(),
    forward: vi.fn(),
    prefetch: vi.fn(),
  }),
  usePathname: () => '/',
  useSearchParams: () => new URLSearchParams(''),
}));
