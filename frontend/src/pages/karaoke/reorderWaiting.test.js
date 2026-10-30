// v32.2.5: dragging a waiting singer must move ONLY that singer. Runs with `craco test` (jest) or plain `node` (see bottom).
import { reorderWaiting } from "./karaokeFlow";

const Q = (...xs) => xs.map(([id, status], i) => ({ id, status, position: i }));
const names = (ids) => ids.join(" ");

describe("reorderWaiting", () => {
  const withStage = Q(["CUR", "current"], ["A", "waiting"], ["B", "waiting"], ["C", "waiting"], ["D", "waiting"]);

  test("drag C up onto A: only C moves, the singer on stage stays first (the reported bug)", () => {
    expect(names(reorderWaiting(withStage, 2, 0))).toBe("CUR C A B D");
  });
  test("drag A down onto C", () => { expect(names(reorderWaiting(withStage, 0, 2))).toBe("CUR B C A D"); });
  test("drag to the very top and the very bottom", () => {
    expect(names(reorderWaiting(withStage, 3, 0))).toBe("CUR D A B C");
    expect(names(reorderWaiting(withStage, 0, 3))).toBe("CUR B C D A");
  });
  test("swap neighbours", () => { expect(names(reorderWaiting(withStage, 1, 2))).toBe("CUR A C B D"); });
  test("no singer on stage works the same", () => {
    expect(names(reorderWaiting(Q(["A", "waiting"], ["B", "waiting"], ["C", "waiting"]), 2, 0))).toBe("C A B");
  });
  test("stage singer is found by status, not by being first in the list", () => {
    expect(names(reorderWaiting(Q(["A", "waiting"], ["CUR", "current"], ["B", "waiting"], ["C", "waiting"]), 2, 0))).toBe("CUR C A B");
  });
  test("an unsorted list is read in position order", () => {
    const shuffled = [withStage[3], withStage[0], withStage[2], withStage[4], withStage[1]];
    expect(names(reorderWaiting(shuffled, 2, 0))).toBe("CUR C A B D");
  });
  test("nothing to do returns null", () => {
    expect(reorderWaiting(withStage, 1, 1)).toBeNull();
    expect(reorderWaiting(withStage, null, 1)).toBeNull();
    expect(reorderWaiting(withStage, 1, 9)).toBeNull();
    expect(reorderWaiting(withStage, -1, 0)).toBeNull();
    expect(reorderWaiting([], 0, 1)).toBeNull();
  });
  test("every singer is kept, none added or lost", () => {
    const out = reorderWaiting(withStage, 3, 1);
    expect([...out].sort()).toEqual(["A", "B", "C", "CUR", "D"]);
  });
  test("the singer who sings NEXT is the first waiting one after a move", () => {
    const out = reorderWaiting(withStage, 3, 0);
    expect(out.filter((id) => id !== "CUR")[0]).toBe("D");
  });
});
