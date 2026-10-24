import { createContext } from 'react';
import type { Document, Source } from '../types';

export const UIContext = createContext<{ openSource: (source: Source) => void; doc?: Document; error: (text: string) => void }>({ openSource: () => {}, error: () => {} });
