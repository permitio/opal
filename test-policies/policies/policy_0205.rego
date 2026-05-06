package audit.validation.action.deny.policy_0205

# Auto-generated policy 205 (Rego v1 syntax)
# Package: audit.validation.action.deny

# Metadata
metadata := {
    "policy_id": "0205",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0205_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default policy_0205_allowed = false
