package compliance.authentication.resource.check.policy_0922

# Auto-generated policy 922 (Rego v1 syntax)
# Package: compliance.authentication.resource.check

# Metadata
metadata := {
    "policy_id": "0922",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0922_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0922_allowed if {
    input.user.active
    input.resource.public
}
default policy_0922_allowed = false
policy_0922_allowed if {
    input.user.role == "admin"
}
