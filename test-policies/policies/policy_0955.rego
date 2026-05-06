package governance.authorization.context.deny.policy_0955

# Auto-generated policy 955 (Rego v1 syntax)
# Package: governance.authorization.context.deny

# Metadata
metadata := {
    "policy_id": "0955",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0955_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0955_allowed if {
    data.policies.governance.enabled
}
policy_0955_allowed if {
    input.user.role == "admin"
}
default policy_0955_allowed = false
