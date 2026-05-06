package security.enforcement.action.allow.policy_0943

# Auto-generated policy 943 (Rego v1 syntax)
# Package: security.enforcement.action.allow

# Metadata
metadata := {
    "policy_id": "0943",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0943_allowed if {
    data.policies.security.enabled
}
default policy_0943_allowed = false
policy_0943_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
