import { EmptyState } from '@/components/ui';

interface StubPageProps {
  title: string;
  description?: string;
}

export function StubPage({ title, description }: StubPageProps) {
  return (
    <div>
      <header className="mb-4">
        <h1 className="text-[22px] font-medium leading-tight tracking-tight">{title}</h1>
        {description ? <p className="mt-1 text-[12.5px] text-text2">{description}</p> : null}
      </header>
      <EmptyState
        title="Coming soon"
        description="This dashboard view will be built out as part of the staged migration from the HTML prototype."
      />
    </div>
  );
}
