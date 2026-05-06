package governance.enforcement.resource.verify.utils.policy_0700

# Auto-generated policy 700 (Rego v1 syntax)
# Package: governance.enforcement.resource.verify.utils

# Metadata
metadata := {
    "policy_id": "0700",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0700_allowed = false
policy_0700_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0700_allowed if {
    input.user.role == "admin"
}
