package audit.authentication.user.verify.policy_0741

# Auto-generated policy 741 (Rego v1 syntax)
# Package: audit.authentication.user.verify

# Metadata
metadata := {
    "policy_id": "0741",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0741_allowed if {
    data.policies.audit.enabled
}
policy_0741_allowed if {
    input.user.active
    input.resource.public
}
policy_0741_allowed if {
    input.user.role == "admin"
}
policy_0741_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
