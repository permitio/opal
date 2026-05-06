package security.validation.action.allow.policy_0277

# Auto-generated policy 277 (Rego v1 syntax)
# Package: security.validation.action.allow

# Metadata
metadata := {
    "policy_id": "0277",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0277_allowed = false
policy_0277_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
