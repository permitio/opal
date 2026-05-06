package governance.validation.resource.allow.policy_0976

# Auto-generated policy 976 (Rego v1 syntax)
# Package: governance.validation.resource.allow

# Metadata
metadata := {
    "policy_id": "0976",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0976_allowed = false
policy_0976_allowed if {
    input.user.active
    input.resource.public
}
policy_0976_allowed if {
    data.policies.governance.enabled
}
policy_0976_allowed if {
    input.user.role == "admin"
}
