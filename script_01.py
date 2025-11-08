from fastapi import FastAPI
from pydantic import BaseModel
from typing import List, Optional

app = FastAPI()

# what APEX will send
class OrderLine(BaseModel):
    product_name: Optional[str] = None
    quantity: Optional[float] = None
    line_total: Optional[float] = None

class OrderExplainRequest(BaseModel):
    order_id: int
    customer_name: Optional[str] = None
    order_date: Optional[str] = None
    lines: Optional[List[OrderLine]] = None

@app.post("/explain-order")
def explain_order(payload: OrderExplainRequest):
    # build a simple explanation – later you swap this for real AI
    lines_text = ""
    if payload.lines:
        lines_bits = []
        for l in payload.lines:
            lines_bits.append(f"{l.quantity} x {l.product_name} (${l.line_total})")
        lines_text = "; ".join(lines_bits)

    explanation = (
        f"Order {payload.order_id}"
        f" for {payload.customer_name or 'an unknown customer'}"
    )
    if payload.order_date:
        explanation += f" on {payload.order_date}"
    if lines_text:
        explanation += f" contains: {lines_text}."
    else:
        explanation += " has no line items."

    return explanation

