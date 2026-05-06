package governance.validation.resource.deny.policy_0719

# Auto-generated policy 719 (Rego v1 syntax)
# Package: governance.validation.resource.deny

# Metadata
metadata := {
    "policy_id": "0719",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0719_allowed if {
    data.policies.governance.enabled
}
default policy_0719_allowed = false
policy_0719_allowed if {
    input.user.role == "admin"
}
