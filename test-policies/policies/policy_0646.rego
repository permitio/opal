package security.authentication.action.validate.data.policy_0646

# Auto-generated policy 646 (Rego v1 syntax)
# Package: security.authentication.action.validate.data

# Metadata
metadata := {
    "policy_id": "0646",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0646_allowed = false
policy_0646_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0646_allowed if {
    input.user.role == "admin"
}
policy_0646_allowed if {
    data.policies.security.enabled
}
