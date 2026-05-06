package governance.enforcement.resource.validate.policy_0560

# Auto-generated policy 560 (Rego v1 syntax)
# Package: governance.enforcement.resource.validate

# Metadata
metadata := {
    "policy_id": "0560",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0560_allowed if {
    input.user.active
    input.resource.public
}
policy_0560_allowed if {
    data.policies.governance.enabled
}
policy_0560_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
