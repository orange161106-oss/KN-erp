import '@testing-library/jest-dom/vitest';
import { afterEach, beforeEach } from 'vitest';
import { cleanup } from '@testing-library/react';
import { setAccessToken, setUnauthorizedHandler } from '../api/client';
// Each test owns a fresh session, including any unfinished shared reads.
beforeEach(() => { setAccessToken(null); setUnauthorizedHandler(null); });
afterEach(cleanup);
