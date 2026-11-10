import { describe, it, expect } from 'vitest';
import { HistoryManager } from '../src/core/history.ts';

describe('HistoryManager (Undo/Redo)', () => {
  it('should initialize empty', () => {
    const history = new HistoryManager();
    expect(history.canUndo()).toBe(false);
    expect(history.canRedo()).toBe(false);
  });

  it('should push and execute undo/redo', () => {
    const history = new HistoryManager();
    let state = 0;

    const action = {
      name: 'Add 1',
      execute: () => { state += 1; },
      undo: () => { state -= 1; },
    };

    history.push(action);
    action.execute();
    expect(state).toBe(1);
    expect(history.canUndo()).toBe(true);

    // Undo
    history.undo();
    expect(state).toBe(0);
    expect(history.canRedo()).toBe(true);

    // Redo
    history.redo();
    expect(state).toBe(1);
  });

  it('should cap stack at maxSize (50 actions)', () => {
    const history = new HistoryManager(50);
    for (let i = 0; i < 60; i++) {
      history.push({
        name: `Action ${i}`,
        execute: () => {},
        undo: () => {},
      });
    }
    expect(history.getUndoCount()).toBe(50);
  });
});

