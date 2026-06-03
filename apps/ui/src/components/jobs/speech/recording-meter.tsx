const METER_BARS = [
  { id: 'a', scale: 0.6 },
  { id: 'b', scale: 1 },
  { id: 'c', scale: 0.8 },
  { id: 'd', scale: 0.45 },
];

export function RecordingMeter({ level }: { level: number }) {
  return (
    <span className="flex items-center gap-0.5" aria-hidden>
      {METER_BARS.map((bar) => (
        <span
          key={bar.id}
          className="w-0.5 rounded-full bg-current"
          style={{
            height: `${Math.max(3, Math.min(16, level * 16 * bar.scale))}px`,
          }}
        />
      ))}
    </span>
  );
}
