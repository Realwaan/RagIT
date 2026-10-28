import { createContext } from 'react';
import type { Source } from './types';

export const EvidenceContext = createContext<{ sources: Source[]; open: (s: Source) => void }>({ sources: [], open: () => {} });
