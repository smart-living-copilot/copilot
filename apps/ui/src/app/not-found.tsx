import { FileQuestion } from 'lucide-react';

import { ErrorState } from '@/components/error-state';

export default function NotFound() {
  return (
    <ErrorState
      description="That address does not match anything in the app."
      icon={FileQuestion}
      title="Page not found"
    />
  );
}
