/** Notification activity — from notification.* events. */

import { Head } from '@inertiajs/react'
import { ago, dateTime } from '@/js/hooks'
import { Badge, Empty, PageHeader, Table, TBody, TD, TH, THead, TR } from '@/views/ui/kit'

interface Note {
  id: string
  recipient: string
  type: string
  title: string | null
  body: string | null
  channel: string
  severity: string
  delivery_status: string
  read: boolean
  event_id: string
  created_at: string
}

export default function Notifications({ environment, notifications }: { environment: string; notifications: Note[] }) {
  return (
    <>
      <Head title="Notifications" />
      <PageHeader title="Notifications" subtitle={`${environment} · ${notifications.length} recent`} />

      {notifications.length === 0 ? (
        <Empty
          title="No notifications"
          body="Publish notification.created events (data.recipient, data.title, data.channel) and they appear here with delivery status."
        />
      ) : (
        <Table>
          <THead>
            <TR>
              <TH>Recipient</TH>
              <TH>Type</TH>
              <TH>Title</TH>
              <TH>Channel</TH>
              <TH>Delivery</TH>
              <TH>Read</TH>
              <TH align="right">When</TH>
            </TR>
          </THead>
          <TBody>
            {notifications.map((n) => (
              <TR key={n.id}>
                <TD className="mono text-[12px]">{n.recipient}</TD>
                <TD>{n.type}</TD>
                <TD>
                  <a href={`/events/${n.event_id}?env=${environment}`} className="text-ink hover:text-brand">
                    {n.title ?? n.body?.slice(0, 60) ?? '(no title)'}
                  </a>
                </TD>
                <TD><Badge tone="neutral">{n.channel}</Badge></TD>
                <TD>
                  <Badge tone={n.delivery_status === 'delivered' ? 'ok' : n.delivery_status === 'failed' ? 'critical' : 'caution'} dot>
                    {n.delivery_status}
                  </Badge>
                </TD>
                <TD>{n.read ? 'read' : <span className="font-medium text-brand">unread</span>}</TD>
                <TD align="right" title={dateTime(n.created_at)}>{ago(n.created_at)}</TD>
              </TR>
            ))}
          </TBody>
        </Table>
      )}
    </>
  )
}
