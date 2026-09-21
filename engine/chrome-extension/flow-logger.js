/**
 * Sinematica Flow Agent — Centralized Structured Logger
 * Provides multi-channel logging across Console, Side Panel, Ring Buffer, and WebSocket.
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) {
    module.exports = factory();
  } else {
    root.FlowLogger = factory().FlowLogger;
  }
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  const LOG_LEVELS = { DEBUG: 0, INFO: 1, WARN: 2, ERROR: 3 };

  class LoggerInstance {
    constructor(options = {}) {
      this.instanceId = options.instanceId || null;
      this.projectId = options.projectId || null;
      this.wsSender = typeof options.wsSender === 'function' ? options.wsSender : null;
      this.minLevel = options.minLevel || 'DEBUG';
      this.maxEntries = options.maxEntries || 200;
      this.logs = [];
      this.listeners = new Set();
    }

    setContext(ctx = {}) {
      if (ctx.instanceId !== undefined) this.instanceId = ctx.instanceId;
      if (ctx.projectId !== undefined) this.projectId = ctx.projectId;
      if (ctx.wsSender !== undefined) this.wsSender = ctx.wsSender;
    }

    addListener(listener) {
      if (typeof listener === 'function') this.listeners.add(listener);
    }

    removeListener(listener) {
      this.listeners.delete(listener);
    }

    _log(level, tag, message, meta = {}) {
      if (LOG_LEVELS[level] < LOG_LEVELS[this.minLevel]) return null;

      const entry = {
        timestamp: new Date().toISOString(),
        level,
        tag: String(tag || 'GENERAL').toUpperCase(),
        message: String(message || ''),
        instance_id: this.instanceId,
        project_id: this.projectId,
        meta: meta && typeof meta === 'object' ? meta : {},
      };

      this.logs.push(entry);
      if (this.logs.length > this.maxEntries) {
        this.logs.shift();
      }

      if (typeof console !== 'undefined') {
        const formatted = `[${entry.timestamp.slice(11, 23)}] [${entry.tag}] ${entry.message}`;
        if (level === 'ERROR') console.error(formatted, entry.meta);
        else if (level === 'WARN') console.warn(formatted, entry.meta);
        else console.log(formatted, entry.meta);
      }

      for (const listener of this.listeners) {
        try { listener(entry); } catch (_) {}
      }

      if (this.wsSender) {
        try {
          this.wsSender({ type: 'agent_log', data: entry });
        } catch (_) {}
      }

      return entry;
    }

    debug(tag, message, meta) { return this._log('DEBUG', tag, message, meta); }
    info(tag, message, meta) { return this._log('INFO', tag, message, meta); }
    warn(tag, message, meta) { return this._log('WARN', tag, message, meta); }
    error(tag, message, meta) { return this._log('ERROR', tag, message, meta); }

    getRecentLogs(limit = 50) {
      return this.logs.slice(-limit);
    }

    clearLogs() {
      this.logs = [];
    }
  }

  const FlowLogger = {
    createLogger(options) {
      return new LoggerInstance(options);
    }
  };

  return { FlowLogger };
});
