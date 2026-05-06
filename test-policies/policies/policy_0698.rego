package risk.validation.user.deny.data.policy_0698

# Auto-generated policy 698 (Rego v1 syntax)
# Package: risk.validation.user.deny.data

# Metadata
metadata := {
    "policy_id": "0698",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0698_allowed = false
policy_0698_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
