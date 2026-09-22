/**
 * SseTestScreen.tsx
 *
 * Drop this file into your React Native project and add it to your navigator.
 * It connects to GET /v1/stream, displays incoming SSE events live, and
 * lets you test filters.
 *
 * No extra packages required — uses fetch + ReadableStream (built into RN).
 *
 * Usage:
 *   import SseTestScreen from './SseTestScreen';
 *   // add to your stack navigator
 */

import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  FlatList,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';

// ─── Config ──────────────────────────────────────────────────────────────────
const BASE_URL = 'http://localhost:4000';   // change to your machine IP if on device
const PROVIDER_ID = 'bluip';               // change to your provider ID

// ─── Types ───────────────────────────────────────────────────────────────────
type ConnectionStatus = 'idle' | 'connecting' | 'connected' | 'disconnected' | 'error';

interface SseEvent {
  id: string;
  kind: string;
  data: Record<string, unknown>;
  receivedAt: string;
}

// ─── SSE parser ──────────────────────────────────────────────────────────────
// Parses raw SSE text chunks into { id, event, data } objects.
function parseSseChunk(chunk: string): Array<{ id?: string; event?: string; data?: string }> {
  const results: Array<{ id?: string; event?: string; data?: string }> = [];
  const blocks = chunk.split('\n\n');

  for (const block of blocks) {
    if (!block.trim() || block.startsWith(':')) continue; // comments / keepalive
    const frame: { id?: string; event?: string; data?: string } = {};
    for (const line of block.split('\n')) {
      if (line.startsWith('id: '))    frame.id    = line.slice(4);
      if (line.startsWith('event: ')) frame.event = line.slice(7);
      if (line.startsWith('data: '))  frame.data  = line.slice(6);
    }
    if (frame.data !== undefined) results.push(frame);
  }
  return results;
}

// ─── Main component ──────────────────────────────────────────────────────────
export default function SseTestScreen() {
  const [status, setStatus]         = useState<ConnectionStatus>('idle');
  const [events, setEvents]         = useState<SseEvent[]>([]);
  const [errorMsg, setErrorMsg]     = useState('');
  const [propertyId, setPropertyId] = useState('');
  const [kinds, setKinds]           = useState('');
  const [minSeverity, setMinSeverity] = useState('');

  const abortRef    = useRef<AbortController | null>(null);
  const lastEventId = useRef<string | null>(null);

  const disconnect = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    setStatus('disconnected');
  }, []);

  const connect = useCallback(async () => {
    // Build URL with optional filters
    const params = new URLSearchParams();
    if (propertyId.trim()) params.set('property_id', propertyId.trim());
    if (kinds.trim())      params.set('kinds', kinds.trim());
    if (minSeverity.trim()) params.set('min_severity', minSeverity.trim());
    const url = `${BASE_URL}/v1/stream${params.toString() ? '?' + params : ''}`;

    const controller = new AbortController();
    abortRef.current = controller;
    setStatus('connecting');
    setErrorMsg('');

    try {
      const headers: Record<string, string> = {
        'X-Provider-Id': PROVIDER_ID,
        'Accept': 'text/event-stream',
        'Cache-Control': 'no-cache',
      };
      if (lastEventId.current) {
        headers['Last-Event-ID'] = lastEventId.current;
      }

      const response = await fetch(url, {
        method: 'GET',
        headers,
        signal: controller.signal,
        // @ts-ignore — RN fetch supports this to enable streaming
        reactNative: { textStreaming: true },
      });

      if (!response.ok) {
        const body = await response.text();
        throw new Error(`HTTP ${response.status}: ${body}`);
      }

      setStatus('connected');

      const reader = response.body?.getReader();
      if (!reader) throw new Error('No readable body');

      const decoder = new TextDecoder();
      let leftover  = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value, { stream: true });
        const text  = leftover + chunk;
        // Hold anything after the last \n\n — could be a partial frame
        const lastSep = text.lastIndexOf('\n\n');
        if (lastSep === -1) { leftover = text; continue; }
        leftover = text.slice(lastSep + 2);

        const frames = parseSseChunk(text.slice(0, lastSep + 2));
        for (const frame of frames) {
          if (frame.id) lastEventId.current = frame.id;
          let parsed: Record<string, unknown> = {};
          try { parsed = JSON.parse(frame.data ?? '{}'); } catch {}

          const ev: SseEvent = {
            id:         frame.id ?? `local-${Date.now()}`,
            kind:       frame.event ?? parsed.event_kind as string ?? 'unknown',
            data:       parsed,
            receivedAt: new Date().toISOString(),
          };
          setEvents(prev => [ev, ...prev].slice(0, 100)); // keep last 100
        }
      }

      setStatus('disconnected');
    } catch (err: unknown) {
      if ((err as Error).name === 'AbortError') {
        setStatus('disconnected');
      } else {
        setErrorMsg((err as Error).message);
        setStatus('error');
      }
    }
  }, [propertyId, kinds, minSeverity]);

  // Clean up on unmount
  useEffect(() => () => { abortRef.current?.abort(); }, []);

  const clearEvents = () => setEvents([]);

  return (
    <View style={s.root}>
      {/* ── Header ── */}
      <Text style={s.title}>SSE Stream Tester</Text>
      <Text style={s.subtitle}>{BASE_URL}/v1/stream</Text>

      {/* ── Filters ── */}
      <View style={s.filterRow}>
        <TextInput
          style={s.input}
          placeholder="property_id (e.g. 123,456)"
          value={propertyId}
          onChangeText={setPropertyId}
          editable={status !== 'connected'}
          placeholderTextColor="#888"
        />
        <TextInput
          style={s.input}
          placeholder="kinds (e.g. alert.opened)"
          value={kinds}
          onChangeText={setKinds}
          editable={status !== 'connected'}
          placeholderTextColor="#888"
        />
        <TextInput
          style={s.input}
          placeholder="min_severity (p1/p2/p3/p4)"
          value={minSeverity}
          onChangeText={setMinSeverity}
          editable={status !== 'connected'}
          placeholderTextColor="#888"
        />
      </View>

      {/* ── Connect / Disconnect buttons ── */}
      <View style={s.btnRow}>
        <Pressable
          style={[s.btn, s.btnConnect, status === 'connected' && s.btnDisabled]}
          onPress={connect}
          disabled={status === 'connected' || status === 'connecting'}
        >
          <Text style={s.btnText}>
            {status === 'connecting' ? 'Connecting...' : 'Connect'}
          </Text>
        </Pressable>

        <Pressable
          style={[s.btn, s.btnDisconnect, status !== 'connected' && s.btnDisabled]}
          onPress={disconnect}
          disabled={status !== 'connected'}
        >
          <Text style={s.btnText}>Disconnect</Text>
        </Pressable>

        <Pressable style={[s.btn, s.btnClear]} onPress={clearEvents}>
          <Text style={s.btnText}>Clear</Text>
        </Pressable>
      </View>

      {/* ── Status badge ── */}
      <View style={[s.statusBadge, statusColor(status)]}>
        <Text style={s.statusText}>
          {status.toUpperCase()}
          {status === 'connected' ? `  •  ${events.length} events` : ''}
        </Text>
      </View>

      {errorMsg ? <Text style={s.error}>{errorMsg}</Text> : null}

      {/* ── Event list ── */}
      <FlatList
        data={events}
        keyExtractor={item => item.id}
        style={s.list}
        ListEmptyComponent={
          <Text style={s.empty}>No events yet. Connect and wait for activity.</Text>
        }
        renderItem={({ item }) => <EventCard event={item} />}
      />
    </View>
  );
}

// ─── Event card ──────────────────────────────────────────────────────────────
function EventCard({ event }: { event: SseEvent }) {
  const [expanded, setExpanded] = useState(false);
  const sev = (event.data.severity as string) ?? '';

  return (
    <Pressable onPress={() => setExpanded(e => !e)} style={s.card}>
      <View style={s.cardHeader}>
        <View style={[s.kindBadge, kindColor(event.kind)]}>
          <Text style={s.kindText}>{event.kind}</Text>
        </View>
        {sev ? <Text style={[s.sev, sevColor(sev)]}>{sev.toUpperCase()}</Text> : null}
        <Text style={s.ts}>{event.receivedAt.slice(11, 19)}</Text>
      </View>

      {event.data.summary ? (
        <Text style={s.summary} numberOfLines={expanded ? undefined : 1}>
          {event.data.summary as string}
        </Text>
      ) : null}

      {expanded && (
        <ScrollView horizontal>
          <Text style={s.json}>
            {JSON.stringify(event.data, null, 2)}
          </Text>
        </ScrollView>
      )}
    </Pressable>
  );
}

// ─── Colour helpers ───────────────────────────────────────────────────────────
function statusColor(s: ConnectionStatus) {
  return {
    idle:         { backgroundColor: '#555' },
    connecting:   { backgroundColor: '#e6a817' },
    connected:    { backgroundColor: '#2e7d32' },
    disconnected: { backgroundColor: '#555' },
    error:        { backgroundColor: '#c62828' },
  }[s];
}

function kindColor(kind: string) {
  if (kind.startsWith('alert'))      return { backgroundColor: '#b71c1c' };
  if (kind.startsWith('auto_fix'))   return { backgroundColor: '#6a1b9a' };
  if (kind.startsWith('device'))     return { backgroundColor: '#1565c0' };
  if (kind.startsWith('edge'))       return { backgroundColor: '#1b5e20' };
  return { backgroundColor: '#37474f' };
}

function sevColor(sev: string) {
  return {
    p1: { color: '#ef5350' },
    p2: { color: '#ffa726' },
    p3: { color: '#ffee58' },
    p4: { color: '#aaa' },
  }[sev] ?? { color: '#aaa' };
}

// ─── Styles ───────────────────────────────────────────────────────────────────
const s = StyleSheet.create({
  root:        { flex: 1, backgroundColor: '#121212', padding: 12 },
  title:       { color: '#fff', fontSize: 18, fontWeight: '700', marginTop: 8 },
  subtitle:    { color: '#888', fontSize: 11, marginBottom: 10 },

  filterRow:   { gap: 6, marginBottom: 10 },
  input: {
    backgroundColor: '#1e1e1e',
    color: '#fff',
    borderRadius: 6,
    padding: 8,
    fontSize: 12,
    borderWidth: 1,
    borderColor: '#333',
  },

  btnRow:      { flexDirection: 'row', gap: 8, marginBottom: 10 },
  btn:         { flex: 1, padding: 10, borderRadius: 6, alignItems: 'center' },
  btnConnect:  { backgroundColor: '#1565c0' },
  btnDisconnect: { backgroundColor: '#b71c1c' },
  btnClear:    { backgroundColor: '#37474f' },
  btnDisabled: { opacity: 0.4 },
  btnText:     { color: '#fff', fontWeight: '600', fontSize: 13 },

  statusBadge: { borderRadius: 4, padding: 6, marginBottom: 6, alignItems: 'center' },
  statusText:  { color: '#fff', fontWeight: '700', fontSize: 12 },

  error:       { color: '#ef5350', fontSize: 12, marginBottom: 6 },

  list:        { flex: 1 },
  empty:       { color: '#555', textAlign: 'center', marginTop: 40, fontSize: 13 },

  card: {
    backgroundColor: '#1e1e1e',
    borderRadius: 8,
    padding: 10,
    marginBottom: 8,
    borderLeftWidth: 3,
    borderLeftColor: '#333',
  },
  cardHeader:  { flexDirection: 'row', alignItems: 'center', gap: 8, flexWrap: 'wrap' },
  kindBadge:   { borderRadius: 4, paddingHorizontal: 6, paddingVertical: 2 },
  kindText:    { color: '#fff', fontSize: 10, fontWeight: '700' },
  sev:         { fontSize: 11, fontWeight: '700' },
  ts:          { color: '#666', fontSize: 10, marginLeft: 'auto' },
  summary:     { color: '#ccc', fontSize: 12, marginTop: 4 },
  json: {
    color: '#80cbc4',
    fontSize: 10,
    fontFamily: 'monospace',
    marginTop: 6,
    lineHeight: 16,
  },
});
