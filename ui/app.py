
"""WorthIt — NLP-Based Personalized Product Recommendation System.

Provides top-three purchase advice, plain-English pros and cons,
and a comparison of rankings with and without bounded-sacrifice floors.
"""
import pathlib
import sys

import streamlit as st

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from core.config import (
    ASPECT_LABELS,
    FLOOR_LAMBDA,
    FLOOR_PERCENTILE,
    PRICE_WEIGHT,
    RANKING_ASPECTS,
)
from core.db import get_session
from core.parser import _keyword_fallback as parse
from core.ranker import rank
from core.retrieve import fetch_candidates


st.set_page_config(
    page_title="WorthIt — Purchase Decision System",
    layout="wide",
)

EXAMPLES = [
    "laptop under 80000 with great performance, dont mind heating",
    "laptop under 60000 with good battery life, performance can be average",
    "laptop under 100000 with great performance and good display",
    "laptop under 50000 with good display, dont mind build quality",
]


# ------------------------------------------------ Plain-English explanations

def describe_aspect(aspect, score, mentions):
    """Convert an internal aspect score into understandable language."""
    label = ASPECT_LABELS.get(aspect, aspect).lower()

    if mentions < 3:
        return (
            f"There are only a few reviews discussing {label}, "
            "so we cannot judge it confidently."
        )

    if score >= 0.80:
        return (
            f"{label.capitalize()} appears to be a strength, "
            "based on the available reviews."
        )

    if score >= 0.65:
        return f"Reviews are generally positive about {label}."

    if score >= 0.45:
        return (
            f"Feedback about {label} appears mixed. "
            "You may want to look into this aspect further."
        )

    return (
        f"{label.capitalize()} may be a weakness, "
        "based on the available reviews."
    )


def get_purchase_advice(product, priorities, floors):
    """Generate explainable BUY, WAIT or SKIP advice."""
    aspects = product.get("aspects", {})
    pros = []
    cons = []
    priority_scores = []
    missing_priority = False

    # Assess aspects explicitly prioritised by the user.
    for aspect in priorities:
        entry = aspects.get(aspect)
        label = ASPECT_LABELS.get(aspect, aspect).lower()

        if not entry or entry.get("mentions", 0) < 3:
            missing_priority = True
            cons.append(
                f"There is not enough review evidence to judge "
                f"{label} confidently."
            )
            continue

        score = float(entry["score"])
        mentions = entry.get("mentions", 0)
        priority_scores.append(score)

        explanation = describe_aspect(aspect, score, mentions)

        if score >= 0.65:
            pros.append(explanation)
        else:
            cons.append(explanation)

    # Include other notable strengths and weaknesses.
    for aspect in RANKING_ASPECTS:
        if aspect in priorities:
            continue

        entry = aspects.get(aspect)
        if not entry or entry.get("mentions", 0) < 3:
            continue

        score = float(entry["score"])
        mentions = entry.get("mentions", 0)

        if score >= 0.80:
            pros.append(describe_aspect(aspect, score, mentions))
        elif score < 0.40:
            cons.append(describe_aspect(aspect, score, mentions))

    # Keep the decision rules transparent and consistent.
    if not priorities:
        verdict = "WAIT"
        reason = (
            "We could not identify a clear priority in your request. "
            "Try specifying what matters most to you."
        )

    elif any(score < 0.45 for score in priority_scores):
        verdict = "SKIP"
        reason = (
            "An important aspect you prioritised has received weak "
            "feedback in the available reviews."
        )

    elif missing_priority or len(priority_scores) != len(priorities):
        verdict = "WAIT"
        reason = (
            "There is not enough review evidence to assess all "
            "your priority aspects confidently."
        )

    elif any(score < 0.70 for score in priority_scores):
        verdict = "WAIT"
        reason = (
            "The product has potential, but at least one of your "
            "priority aspects needs closer consideration."
        )

    elif product.get("floor_penalty", 0) > 0:
        verdict = "WAIT"
        reason = (
            "The product falls below the minimum level set for "
            "an aspect you said you could compromise on."
        )

    else:
        verdict = "BUY"
        reason = (
            "The available reviews look positive for the aspects "
            "you prioritised, with sufficient evidence to assess them."
        )

    if not pros:
        pros.append(
            "The available reviews do not establish a clear strength."
        )

    if not cons:
        cons.append(
            "No major weakness was identified in the aspects assessed. "
            "This does not guarantee that the product has no drawbacks."
        )

    return verdict, reason, pros, cons


# ------------------------------------------------ Product comparison cards

def card(rank_pos, product, floors, moved=None):
    """Display the technical ranking details for a product."""
    penalised = product.get("floor_penalty", 0) > 0

    with st.container(border=True):
        title = (
            product.get("title", "Unknown product")[:100]
            .replace("*", "")
            .replace("_", "")
        )

        heading = f"**{rank_pos}. {title}**"
        if penalised:
            heading += " 🔻"

        st.markdown(heading)

        price = product.get("price")
        price_text = (
            f"₹{price:,.0f}" if price is not None else "Price unavailable"
        )

        details = [price_text]

        if moved is not None and moved != 0:
            details.append(f"Rank change: {moved:+d} places")

        st.caption(" • ".join(details))

        for aspect in RANKING_ASPECTS:
            entry = product.get("aspects", {}).get(aspect)
            if not entry:
                continue

            label = ASPECT_LABELS.get(aspect, aspect)
            score = float(entry["score"])
            mentions = entry.get("mentions", 0)
            floor_value = floors.get(aspect)

            floor_note = ""
            if floor_value is not None:
                if score < floor_value:
                    floor_note = " — below minimum"
                else:
                    floor_note = " — meets minimum"

            st.progress(
                min(1.0, max(0.0, score)),
                text=(
                    f"{label}: {score:.2f} "
                    f"({mentions} mentions){floor_note}"
                ),
            )

        if penalised:
            st.warning(
                "This product received a ranking penalty because it "
                "fell below an applicable sacrifice floor."
            )


# ------------------------------------------------------------------ Header

st.title(
    "WorthIt — NLP-Based Personalized Product Recommendation "
    "& Purchase Decision System"
)
st.caption(
    "Find products that match your priorities without compromising "
    "on the things that matter most."
)


# ------------------------------------------------------------------ Sidebar

with st.sidebar:
    st.header("Parameters")
    st.metric("Floor percentile", f"{FLOOR_PERCENTILE:.0f}")
    st.metric("Floor penalty λ", f"{FLOOR_LAMBDA:.1f}")
    st.metric("Price weight", f"{PRICE_WEIGHT:.2f}")

    st.divider()

    use_price = st.checkbox("Price efficiency", value=True)
    top_k = st.slider("Results to show", 3, 10, 5)

    st.divider()
    st.caption("Ranking aspects:")

    for aspect in RANKING_ASPECTS:
        st.caption(f"• {ASPECT_LABELS.get(aspect, aspect)}")


# -------------------------------------------------------------------- Query

query_col, example_col = st.columns([3, 2])

with example_col:
    picked = st.selectbox("Example queries", [""] + EXAMPLES)

with query_col:
    query = st.text_input(
        "Your query",
        value=picked or EXAMPLES[0],
    )

go = st.button(
    "Recommend",
    type="primary",
    use_container_width=True,
)


# --------------------------------------------------------------------- Main

if go and query.strip():
    parsed = parse(query)

    if parsed.constraints.max_price is None:
        st.warning(
            "No budget detected. Try wording like "
            "'laptop under 80000'."
        )
        st.stop()

    priorities = list(parsed.priorities())
    sacrifices = parsed.sacrifices()

    info1, info2, info3 = st.columns(3)

    info1.metric(
        "Budget",
        f"₹{parsed.constraints.max_price:,.0f}",
    )
    info2.metric(
        "Priority",
        ", ".join(
            ASPECT_LABELS.get(a, a) for a in priorities
        ) or "Not detected",
    )
    info3.metric(
        "Willing to sacrifice",
        ", ".join(
            ASPECT_LABELS.get(a, a) for a in sacrifices
        ) or "None detected",
    )

    if not sacrifices:
        st.info(
            "No sacrifice was detected. The floor only applies to "
            "aspects you explicitly agree to compromise on."
        )

    with get_session() as session:
        candidates = fetch_candidates(
            session,
            parsed.constraints,
        )

    if not candidates:
        st.error("No laptops matched your budget.")
        st.stop()

    st.caption(
        f"{len(candidates)} laptops passed the budget filter."
    )

    # Baseline ranking without the bounded-sacrifice floor.
    without_floor, _ = rank(
        candidates,
        parsed,
        use_floor=False,
        use_price=use_price,
        top_k=len(candidates),
    )

    # Main ranking with the degeneracy guard enabled.
    with_floor, floors = rank(
        candidates,
        parsed,
        use_floor=True,
        use_price=use_price,
        top_k=len(candidates),
        guard=True,
    )

    baseline_positions = {
        product["product_id"]: position
        for position, product in enumerate(without_floor, 1)
    }

    # ------------------------------------------------ Purchase recommendations

    st.divider()
    st.header("Your top 3 purchase recommendations")
    st.caption(
        "Simple explanations based on your priorities and the available "
        "review evidence. BUY, WAIT and SKIP are rule-based guidance."
    )

    for position, product in enumerate(with_floor[:3], 1):
        verdict, reason, pros, cons = get_purchase_advice(
            product,
            priorities,
            floors,
        )

        with st.container(border=True):
            product_col, verdict_col = st.columns([4, 1])

            with product_col:
                title = product.get("title", "Unknown product")
                st.subheader(f"#{position} — {title}")

                price = product.get("price")
                if price is None:
                    st.write("**Price:** Unavailable")
                else:
                    st.write(f"**Price:** ₹{price:,.0f}")

            with verdict_col:
                if verdict == "BUY":
                    st.success("BUY")
                elif verdict == "WAIT":
                    st.warning("WAIT")
                else:
                    st.error("SKIP")

            st.write(f"**Why this recommendation?** {reason}")

            pros_col, cons_col = st.columns(2)

            with pros_col:
                st.markdown("**Pros**")
                for item in pros[:4]:
                    st.markdown(f"- ✅ {item}")

            with cons_col:
                st.markdown("**Cons**")
                for item in cons[:4]:
                    st.markdown(f"- ⚠️ {item}")

            st.caption(
                "These explanations summarise aspect scores derived from "
                "reviews. They are not direct quotations from reviewers."
            )

    # ------------------------------------------------ Floor comparison

    st.divider()
    st.header("How the sacrifice floor changes recommendations")

    if floors:
        st.info(
            "Applicable minimum levels were calculated from the "
            "current candidate pool. The ranking may penalise products "
            "that fall below these levels."
        )
    elif sacrifices:
        st.info(
            "No applicable sacrifice floors were produced for this query."
        )

    left, right = st.columns(2)

    with left:
        st.subheader("Without floor")
        st.caption(
            "Sacrificed aspects do not receive a floor penalty."
        )

        for position, product in enumerate(without_floor[:top_k], 1):
            card(position, product, {})

    with right:
        st.subheader("With floor (guarded)")
        st.caption(
            "Applicable sacrifice floors can penalise products that "
            "fall below the calculated minimum."
        )

        for position, product in enumerate(with_floor[:top_k], 1):
            previous_position = baseline_positions.get(
                product["product_id"],
                position,
            )
            movement = previous_position - position

            card(
                position,
                product,
                floors,
                moved=movement,
            )

    # ------------------------------------------------ Explain ranking changes

    demoted = []

    for new_position, product in enumerate(with_floor, 1):
        product_id = product["product_id"]

        if product_id not in baseline_positions:
            continue

        old_position = baseline_positions[product_id]

        if (
            new_position > old_position
            and product.get("floor_penalty", 0) > 0
        ):
            demoted.append(
                (old_position, new_position, product)
            )

    st.divider()

    if demoted:
        st.subheader("Products moved down because of a sacrifice floor")

        for old_position, new_position, product in sorted(
            demoted,
            key=lambda item: item[1] - item[0],
            reverse=True,
        ):
            affected = []

            for aspect in sacrifices:
                entry = product.get("aspects", {}).get(aspect)
                floor_value = floors.get(aspect)

                if (
                    entry
                    and floor_value is not None
                    and entry["score"] < floor_value
                ):
                    affected.append(
                        ASPECT_LABELS.get(aspect, aspect).lower()
                    )

            title = product.get("title", "Unknown product")
            if affected:
                explanation = (
                    "It fell below the minimum for "
                    + ", ".join(affected)
                    + "."
                )
            else:
                explanation = (
                    "It received a penalty on an applicable "
                    "sacrifice floor."
                )

            st.markdown(
                f"**{title}** — rank {old_position} to "
                f"{new_position}. {explanation}"
            )

    else:
        st.info(
            "No products were demoted by the floor for this query. "
            "The floor may not change every ranking."
        )
