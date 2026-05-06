package risk.authentication.context.allow.policy_0744

# Auto-generated policy 744 (Rego v1 syntax)
# Package: risk.authentication.context.allow

# Metadata
metadata := {
    "policy_id": "0744",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0744_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0744_allowed if {
    input.user.active
    input.resource.public
}
policy_0744_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default policy_0744_allowed = false
