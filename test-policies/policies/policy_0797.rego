package audit.enforcement.user.validate.policy_0797

# Auto-generated policy 797 (Rego v1 syntax)
# Package: audit.enforcement.user.validate

# Metadata
metadata := {
    "policy_id": "0797",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0797_allowed if {
    input.user.role == "admin"
}
policy_0797_allowed if {
    data.policies.audit.enabled
}
policy_0797_allowed if {
    input.user.active
    input.resource.public
}
