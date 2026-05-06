package compliance.validation.policy.deny.logic.policy_0254

# Auto-generated policy 254 (Rego v1 syntax)
# Package: compliance.validation.policy.deny.logic

# Metadata
metadata := {
    "policy_id": "0254",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0254_allowed = false
policy_0254_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
