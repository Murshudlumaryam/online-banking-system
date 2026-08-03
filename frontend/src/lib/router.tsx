/* eslint-disable react-refresh/only-export-components -- small in-house router exports hooks and components together */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import type { AnchorHTMLAttributes, ReactElement, ReactNode } from "react";

interface RouteObject {
  path?: string;
  index?: boolean;
  element: ReactElement;
  children?: RouteObject[];
}

interface Router {
  routes: RouteObject[];
}

interface NavigateOptions {
  replace?: boolean;
  state?: unknown;
}

interface LocationLike {
  pathname: string;
  state: unknown;
}

interface RouterContextValue {
  location: LocationLike;
  navigate: (to: string, options?: NavigateOptions) => void;
  params: Record<string, string>;
}

const RouterContext = createContext<RouterContextValue | null>(null);
const OutletContext = createContext<ReactNode>(null);

export function createBrowserRouter(routes: RouteObject[]): Router {
  return { routes };
}

function currentLocation(): LocationLike {
  return {
    pathname: window.location.pathname,
    state: window.history.state?.usr ?? null,
  };
}

function resolvePath(to: string, from: string): string {
  if (to.startsWith("/")) return to;
  const base = from.endsWith("/") ? from : `${from}/`;
  return new URL(to, `${window.location.origin}${base}`).pathname;
}

export function RouterProvider({ router }: { router: Router }) {
  const [location, setLocation] = useState<LocationLike>(() => currentLocation());

  useEffect(() => {
    function handlePopState() {
      setLocation(currentLocation());
    }
    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, []);

  const navigate = useCallback(
    (to: string, options: NavigateOptions = {}) => {
      const pathname = resolvePath(to, location.pathname);
      const state = { usr: options.state ?? null };
      if (options.replace) {
        window.history.replaceState(state, "", pathname);
      } else {
        window.history.pushState(state, "", pathname);
      }
      setLocation({ pathname, state: state.usr });
    },
    [location.pathname],
  );

  const match = useMemo(() => matchRoutes(router.routes, location.pathname), [router.routes, location.pathname]);
  const value = useMemo(
    () => ({ location, navigate, params: match.params }),
    [location, match.params, navigate],
  );

  return <RouterContext.Provider value={value}>{match.element}</RouterContext.Provider>;
}

export function MemoryRouter({ children, initialEntries }: { children: ReactNode; initialEntries?: string[] }) {
  const initialPath = initialEntries?.[0] ?? "/";
  const [location, setLocation] = useState<LocationLike>({ pathname: initialPath, state: null });
  const navigate = useCallback((to: string, options: NavigateOptions = {}) => {
    void options;
    setLocation({ pathname: to, state: options.state ?? null });
  }, []);
  const value = useMemo(() => ({ location, navigate, params: {} }), [location, navigate]);
  return <RouterContext.Provider value={value}>{children}</RouterContext.Provider>;
}

export function Outlet() {
  return <>{useContext(OutletContext)}</>;
}

export function useNavigate() {
  return useRouter().navigate;
}

export function useLocation() {
  return useRouter().location;
}

export function useParams<TParams extends Record<string, string | undefined> = Record<string, string>>() {
  return useRouter().params as TParams;
}

export function Navigate({ to, replace, state }: { to: string; replace?: boolean; state?: unknown }) {
  const navigate = useNavigate();
  useEffect(() => {
    navigate(to, { replace, state });
  }, [navigate, replace, state, to]);
  return null;
}

export function Link({
  to,
  children,
  onClick,
  ...props
}: AnchorHTMLAttributes<HTMLAnchorElement> & { to: string }) {
  const navigate = useNavigate();
  return (
    <a
      {...props}
      href={to}
      onClick={(event) => {
        onClick?.(event);
        if (!event.defaultPrevented && event.button === 0 && !event.metaKey && !event.ctrlKey && !event.shiftKey) {
          event.preventDefault();
          navigate(to);
        }
      }}
    >
      {children}
    </a>
  );
}

export function NavLink({
  to,
  className,
  children,
}: {
  to: string;
  className?: string | ((state: { isActive: boolean }) => string);
  children: ReactNode;
}) {
  const { location } = useRouter();
  const isActive = location.pathname === to || location.pathname.startsWith(`${to}/`);
  const resolvedClassName = typeof className === "function" ? className({ isActive }) : className;
  return (
    <Link to={to} className={resolvedClassName}>
      {children}
    </Link>
  );
}

function useRouter(): RouterContextValue {
  const context = useContext(RouterContext);
  if (!context) throw new Error("Router context is missing");
  return context;
}

function matchRoutes(routes: RouteObject[], pathname: string): { element: ReactNode; params: Record<string, string> } {
  const segments = trim(pathname).split("/").filter(Boolean);
  const match = matchBranch(routes, segments, 0, {});
  return match ?? { element: null, params: {} };
}

function matchBranch(
  routes: RouteObject[],
  segments: string[],
  index: number,
  params: Record<string, string>,
): { element: ReactNode; params: Record<string, string> } | null {
  for (const route of routes) {
    if (route.index) {
      if (index === segments.length) return { element: route.element, params };
      continue;
    }

    if (route.path === "*") return { element: route.element, params };

    const routeSegments = trim(route.path ?? "").split("/").filter(Boolean);
    const start = route.path?.startsWith("/") ? 0 : index;
    const nextParams = { ...params };
    if (!segmentsMatch(routeSegments, segments, start, nextParams)) continue;

    const nextIndex = start + routeSegments.length;
    if (route.children) {
      const child = matchBranch(route.children, segments, nextIndex, nextParams);
      if (child) {
        return {
          params: child.params,
          element: <OutletContext.Provider value={child.element}>{route.element}</OutletContext.Provider>,
        };
      }
    }

    if (nextIndex === segments.length) return { element: route.element, params: nextParams };
  }
  return null;
}

function segmentsMatch(
  routeSegments: string[],
  pathSegments: string[],
  start: number,
  params: Record<string, string>,
): boolean {
  if (routeSegments.length === 0) return start === 0 || pathSegments.length === 0;
  if (start + routeSegments.length > pathSegments.length) return false;
  for (let offset = 0; offset < routeSegments.length; offset += 1) {
    const routeSegment = routeSegments[offset];
    const pathSegment = pathSegments[start + offset];
    if (routeSegment.startsWith(":")) {
      params[routeSegment.slice(1)] = decodeURIComponent(pathSegment);
      continue;
    }
    if (routeSegment !== pathSegment) return false;
  }
  return true;
}

function trim(path = ""): string {
  return path.replace(/^\/+|\/+$/g, "");
}

