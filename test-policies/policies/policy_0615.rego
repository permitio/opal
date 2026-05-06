package access.enforcement.resource.validate.policy_0615

# Auto-generated policy 615 (Rego v1 syntax)
# Package: access.enforcement.resource.validate

# Metadata
metadata := {
    "policy_id": "0615",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0615_allowed if {
    input.user.active
    input.resource.public
}
policy_0615_allowed if {
    data.policies.access.enabled
}
policy_0615_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
