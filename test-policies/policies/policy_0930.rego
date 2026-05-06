package access.validation.context.verify.helpers.policy_0930

# Auto-generated policy 930 (Rego v1 syntax)
# Package: access.validation.context.verify.helpers

# Metadata
metadata := {
    "policy_id": "0930",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0930_allowed if {
    input.user.role == "admin"
}
policy_0930_allowed if {
    input.user.active
    input.resource.public
}
policy_0930_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0930_allowed if {
    data.policies.access.enabled
}
