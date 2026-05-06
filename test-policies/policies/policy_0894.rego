package risk.validation.context.deny.data.policy_0894

# Auto-generated policy 894 (Rego v1 syntax)
# Package: risk.validation.context.deny.data

# Metadata
metadata := {
    "policy_id": "0894",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0894_allowed = false
policy_0894_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
