import { useQuery } from "@tanstack/react-query";
import { useAppVersion } from "../lib/useAppVersion";
import { entitlementApi } from "../services/entitlementApi";
import {
  buildProductEditionState,
  ENTITLEMENTS_QUERY_KEY,
  type ProductEditionState,
} from "../services/productEdition";

/** Global StoryLens free/pro identity — single entitlement query shared by shell + settings. */
export function useProductEdition(): ProductEditionState {
  const applicationVersion = useAppVersion();
  const query = useQuery({
    queryKey: ENTITLEMENTS_QUERY_KEY,
    queryFn: entitlementApi.snapshot,
    staleTime: 30_000,
    retry: false,
  });

  return buildProductEditionState({
    snapshot: query.data,
    loaded: query.isFetched || query.isError,
    error: query.isError ? query.error : null,
    applicationVersion,
  });
}
