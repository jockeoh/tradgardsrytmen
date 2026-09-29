import { Scope } from '../core/session';
import { ShoppingRow } from './types';

export function localScopeKey(scope: Scope) {
  const origin = 'origin' in scope.transport ? scope.transport.origin : 'synthetic';
  return JSON.stringify([origin, scope.account, scope.garden]);
}

export function undoShopping(current: ShoppingRow[], before: ShoppingRow[], after: ShoppingRow[]) {
  if (JSON.stringify(current) !== JSON.stringify(after))
    throw new Error('Listan har ändrats sedan dess. Uppdatera listan innan du ändrar den igen.');
  return before;
}
