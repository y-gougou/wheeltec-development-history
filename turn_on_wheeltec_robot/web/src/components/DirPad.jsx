import React from 'react';
import {
  ArrowDown, ArrowDownLeft, ArrowDownRight, ArrowLeft,
  ArrowRight, ArrowUp, ArrowUpLeft, ArrowUpRight, Square,
} from 'lucide-react';

const DIRS = [
  { label: 'FL', icon: ArrowUpLeft, x: 1, y: 1 },
  { label: 'F', icon: ArrowUp, x: 1, y: 0 },
  { label: 'FR', icon: ArrowUpRight, x: 1, y: -1 },
  { label: 'L', icon: ArrowLeft, x: 0, y: 1 },
  { label: 'S', icon: Square, x: 0, y: 0 },
  { label: 'R', icon: ArrowRight, x: 0, y: -1 },
  { label: 'BL', icon: ArrowDownLeft, x: -1, y: 1 },
  { label: 'B', icon: ArrowDown, x: -1, y: 0 },
  { label: 'BR', icon: ArrowDownRight, x: -1, y: -1 },
];

export default function DirPad({ value, onChange }) {
  return (
    <div className="dirPad">
      {DIRS.map((item) => {
        const Icon = item.icon;
        const active = value.x === item.x && value.y === item.y;
        return (
          <button
            key={item.label}
            className={active ? 'active' : 'ghost'}
            title={item.label}
            onClick={() => onChange({ x: item.x, y: item.y })}
          >
            <Icon size={18}/>
          </button>
        );
      })}
    </div>
  );
}
