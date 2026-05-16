import { motion } from 'framer-motion';
import { Eraser, Paintbrush, Scissors, Square } from 'lucide-react';
import { useState } from 'react';

const tools = [
  { name: 'Ластик', icon: Eraser, description: 'Стирание маски' },
  { name: 'Кисть', icon: Paintbrush, description: 'Дорисовка сегментов' },
  { name: 'Разделение сегментов', icon: Scissors, description: 'Разрезание склеенных объектов' },
  { name: 'Bounding Box', icon: Square, description: 'Работа с детекцией' }
];

interface SidebarProps {
  selectedTool: string | null;
  onToolSelect: (tool: string) => void;
}

const Sidebar: React.FC<SidebarProps> = ({ selectedTool, onToolSelect }) => {
  const [hoveredTool, setHoveredTool] = useState<string | null>(null);

  return (
    <aside className="hidden w-80 shrink-0 space-y-4 rounded-3xl border border-slate-800 bg-slate-900/80 p-5 lg:block">
      <div className="mb-4 text-sm uppercase tracking-[0.25em] text-slate-500">Инструменты</div>
      {tools.map((tool, idx) => {
        const Icon = tool.icon;
        const isSelected = selectedTool === tool.name;
        return (
          <motion.div
            key={tool.name}
            className={`flex cursor-pointer items-center gap-3 rounded-3xl px-4 py-3 transition ${
              isSelected ? 'bg-brand-500/20 border border-brand-500' : 'text-slate-200 hover:bg-slate-800'
            }`}
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
            onMouseEnter={() => setHoveredTool(tool.name)}
            onMouseLeave={() => setHoveredTool(null)}
            onClick={() => onToolSelect(tool.name)}
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: idx * 0.1 }}
          >
            <Icon size={18} />
            <span>{tool.name}</span>
          </motion.div>
        );
      })}
      {hoveredTool && (
        <motion.div
          className="mt-4 rounded-3xl border border-slate-700 bg-slate-800 p-3 text-sm text-slate-300"
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: 10 }}
        >
          {tools.find(t => t.name === hoveredTool)?.description}
        </motion.div>
      )}
    </aside>
  );
};

export default Sidebar;
