package governance.monitoring.policy.validate.policy_0364

# Auto-generated policy 364 (Rego v1 syntax)
# Package: governance.monitoring.policy.validate

# Metadata
metadata := {
    "policy_id": "0364",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0364_allowed if {
    data.policies.governance.enabled
}
default policy_0364_allowed = false
policy_0364_allowed if {
    input.user.active
    input.resource.public
}
policy_0364_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
