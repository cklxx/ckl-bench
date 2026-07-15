import { useCallback } from "react";
import { useT } from "@/lib/i18n";
import { useToast } from "@/components/ui/toast";

export function useCopyToast() {
  const t = useT();
  const { toast } = useToast();
  return useCallback(
    (e: React.MouseEvent, value: string) => {
      e.stopPropagation();
      navigator.clipboard.writeText(value);
      toast(t("common.copied", { value }));
    },
    [t, toast]
  );
}
