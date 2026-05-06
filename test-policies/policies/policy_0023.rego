package compliance.authorization.resource.allow.policy_0023

# Auto-generated policy 23 (Rego v1 syntax)
# Package: compliance.authorization.resource.allow

# Metadata
metadata := {
    "policy_id": "0023",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0023_allowed if {
    data.policies.compliance.enabled
}
policy_0023_allowed if {
    input.user.role == "admin"
}
policy_0023_allowed if {
    input.user.active
    input.resource.public
}
