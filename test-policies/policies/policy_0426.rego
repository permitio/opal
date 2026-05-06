package governance.authentication.resource.allow.data.policy_0426

# Auto-generated policy 426 (Rego v1 syntax)
# Package: governance.authentication.resource.allow.data

# Metadata
metadata := {
    "policy_id": "0426",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0426_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0426_allowed if {
    input.user.role == "admin"
}
policy_0426_allowed if {
    input.user.active
    input.resource.public
}
