package governance.authorization.policy.verify.core.policy_0540

# Auto-generated policy 540 (Rego v1 syntax)
# Package: governance.authorization.policy.verify.core

# Metadata
metadata := {
    "policy_id": "0540",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0540_allowed if {
    input.user.role == "admin"
}
default policy_0540_allowed = false
policy_0540_allowed if {
    data.policies.governance.enabled
}
