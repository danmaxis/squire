'use client';

import { useState } from 'react';
import { Check, Copy, Terminal } from 'lucide-react';
import type { CliHint } from '@/lib/cliHints';

/**
 * Copia mesmo em HTTP de LAN: navigator.clipboard exige secure context
 * (o deploy real é http://192.168…), então o fallback com execCommand
 * não é opcional.
 */
async function copyText(text: string): Promise<boolean> {
  if (typeof navigator !== 'undefined' && navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch {
      // cai para o fallback
    }
  }
  try {
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.style.position = 'fixed';
    ta.style.opacity = '0';
    document.body.appendChild(ta);
    ta.select();
    const ok = document.execCommand('copy');
    document.body.removeChild(ta);
    return ok;
  } catch {
    return false;
  }
}

export default function CommandChips({ hints }: { hints: CliHint[] }) {
  const [copied, setCopied] = useState<string | null>(null);

  if (hints.length === 0) return null;

  const handleCopy = async (cmd: string) => {
    if (await copyText(cmd)) {
      setCopied(cmd);
      setTimeout(() => setCopied((c) => (c === cmd ? null : c)), 1500);
    }
  };

  return (
    <div className="space-y-1.5" data-testid="command-chips">
      {hints.map((hint) => (
        <div key={hint.cmd} className="flex items-start gap-2">
          <button
            onClick={() => handleCopy(hint.cmd)}
            title={hint.why}
            className="group flex shrink-0 items-center gap-1.5 rounded border border-gray-300 bg-gray-100 px-2 py-1 font-mono text-xs text-gray-800 hover:border-blue-400 hover:bg-blue-50 dark:border-gray-600 dark:bg-gray-700 dark:text-gray-100 dark:hover:bg-gray-600"
          >
            <Terminal className="h-3 w-3 text-gray-400" />
            {hint.cmd}
            {copied === hint.cmd ? (
              <Check className="h-3 w-3 text-green-600 dark:text-green-400" />
            ) : (
              <Copy className="h-3 w-3 text-gray-400 group-hover:text-blue-500" />
            )}
          </button>
          <span className="pt-1 text-xs text-gray-500 dark:text-gray-400">
            {copied === hint.cmd ? 'copiado ✓' : hint.why}
          </span>
        </div>
      ))}
    </div>
  );
}
