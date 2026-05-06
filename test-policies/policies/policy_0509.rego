package access.validation.action.validate.helpers.policy_0509

# Auto-generated policy 509 (Rego v1 syntax)
# Package: access.validation.action.validate.helpers

# Metadata
metadata := {
    "policy_id": "0509",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0509_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0509_allowed if {
    input.user.role == "admin"
}
policy_0509_allowed if {
    data.policies.access.enabled
}
policy_0509_allowed if {
    input.user.active
    input.resource.public
}
