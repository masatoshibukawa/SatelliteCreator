import type { EquipmentCategory } from "../lib/types";

interface EquipmentPanelProps {
  categories: EquipmentCategory[];
  busy: boolean;
  onChoose: (categoryId: string, optionId: string) => void;
}

export default function EquipmentPanel({ categories, busy, onChoose }: EquipmentPanelProps) {
  if (categories.length === 0) return null;

  return (
    <section className="panel equipment" aria-label="搭載機器">
      <h2 className="panel-title">搭載機器（質量と電力は暫定値）</h2>
      {categories.map((category) => (
        <fieldset key={category.id} className="equipment-group">
          <legend>{category.label}</legend>
          <div className="option-list">
            {category.options.map((option) => (
              <button
                key={option.id}
                type="button"
                className="chip-option"
                aria-pressed={option.id === category.selected}
                disabled={busy}
                onClick={() => onChoose(category.id, option.id)}
              >
                {option.label}
              </button>
            ))}
          </div>
        </fieldset>
      ))}
    </section>
  );
}
