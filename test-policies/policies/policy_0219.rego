package risk.enforcement.resource.verify.logic.policy_0219

# Auto-generated policy 219 (Rego v1 syntax)
# Package: risk.enforcement.resource.verify.logic

# Metadata
metadata := {
    "policy_id": "0219",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0219_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
default policy_0219_allowed = false
